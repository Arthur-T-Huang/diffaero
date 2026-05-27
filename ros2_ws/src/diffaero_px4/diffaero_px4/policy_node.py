#!/usr/bin/env python3
"""
DiffAero SHA2C+RCNN policy deployment node for PX4 SITL.

Policy I/O (matches training in obstacle_avoidance.py with obs_frame="local"):
  state [9D]:       [target_vel_local(3), uz_local(3), vel_local(3)]
  perception [9x16]: normalized depth image (0=min, 1=5m max range)

Subscribes to:
  /fmu/out/vehicle_local_position  — NED position + velocity
  /fmu/out/vehicle_attitude        — quaternion
  /depth_camera/depth/image_raw    — depth image from Gazebo sensor (bridged)

Publishes to:
  /fmu/in/offboard_control_mode
  /fmu/in/trajectory_setpoint      — velocity commands in NED
  /fmu/in/vehicle_command          — arm + offboard mode

Frame conventions:
  DiffAero world frame: right-hand, z-up. X = velocity-aligned heading (EMA).
  PX4 / uXRCE-DDS:     NED (x=North, y=East, z=Down).
  ENU conversion:       [N,E,D] <-> [E,N,U] via ned_to_enu() / enu_to_ned().

Control strategy:
  - Policy outputs 3D world-frame acceleration (ENU).
  - Velocity setpoint = v_current + a_cmd * dt, clamped to max_vel.
  - Offboard mode is engaged after 2 s of pre-arm setpoint publishing.
"""

import math
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
)
from sensor_msgs.msg import Image
try:
    from cv_bridge import CvBridge
    HAS_CV_BRIDGE = True
except ImportError:
    HAS_CV_BRIDGE = False
    import struct
import cv2
import onnxruntime as ort

from px4_msgs.msg import (
    VehicleLocalPosition,
    VehicleAttitude,
    TrajectorySetpoint,
    OffboardControlMode,
    VehicleCommand,
)


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------

def ned_to_enu(v: np.ndarray) -> np.ndarray:
    """[N, E, D]  ->  [E, N, U]"""
    return np.array([v[1], v[0], -v[2]], dtype=np.float32)


def enu_to_ned(v: np.ndarray) -> np.ndarray:
    """[E, N, U]  ->  [N, E, D]"""
    return np.array([v[1], v[0], -v[2]], dtype=np.float32)


def yaw_rotation_matrix(yaw: float) -> np.ndarray:
    """3x3 Rz (pure yaw, ENU / z-up right-hand convention)."""
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s, 0.],
                     [s,  c, 0.],
                     [0., 0., 1.]], dtype=np.float32)


def angle_wrap(a: float) -> float:
    """Wrap angle to [-pi, pi]."""
    return (a + math.pi) % (2 * math.pi) - math.pi


def quat_px4_to_yaw_enu(q) -> float:
    """
    PX4 quaternion [w, x, y, z] in NED  ->  yaw in ENU frame.

    NED yaw (from North, clockwise) maps to ENU yaw (from East, CCW) via:
        yaw_enu = pi/2 - yaw_ned
    """
    w, x, y, z = float(q[0]), float(q[1]), float(q[2]), float(q[3])
    yaw_ned = math.atan2(2.0 * (w * z + x * y),
                          1.0 - 2.0 * (y * y + z * z))
    return math.pi / 2.0 - yaw_ned


# ---------------------------------------------------------------------------
# Policy node
# ---------------------------------------------------------------------------

class DiffAeroPolicyNode(Node):
    """
    Runs the exported DiffAero RCNN policy and sends velocity setpoints to PX4.
    """

    # Seconds of setpoints to publish before arming / switching to offboard
    PRE_ARM_SECONDS = 2.0

    def __init__(self):
        super().__init__('diffaero_policy')

        # ---- Declare parameters ----
        self.declare_parameter('onnx_path', '')
        self.declare_parameter('goal_enu', [25.0, 0.0, 1.5])
        self.declare_parameter('max_vel', 4.5)          # m/s (in [3, 6] from training)
        self.declare_parameter('max_acc_xy', 15.0)      # m/s² (training default 20, use 15 for safety)
        self.declare_parameter('max_acc_z', 32.0)       # m/s² (training default 40)
        self.declare_parameter('max_depth_range', 5.0)  # m  (must match sensor.max_dist)
        self.declare_parameter('control_freq', 30.0)    # Hz (matches env dt = 0.0333 s)
        self.declare_parameter('vel_ema_factor', 0.1)   # matches pmc.yaml vel_ema_factor.default
        self.declare_parameter('depth_topic', '/depth_camera/depth/image_raw')
        self.declare_parameter('takeoff_altitude', 1.5) # m AGL before handing over to policy

        onnx_path     = self.get_parameter('onnx_path').value
        self.goal_enu = np.array(self.get_parameter('goal_enu').value, dtype=np.float32)
        self.max_vel  = float(self.get_parameter('max_vel').value)
        self.max_acc_xy    = float(self.get_parameter('max_acc_xy').value)
        self.max_acc_z     = float(self.get_parameter('max_acc_z').value)
        self.max_range     = float(self.get_parameter('max_depth_range').value)
        control_freq       = float(self.get_parameter('control_freq').value)
        self.vel_ema_alpha = float(self.get_parameter('vel_ema_factor').value)
        depth_topic        = self.get_parameter('depth_topic').value
        self.takeoff_alt   = float(self.get_parameter('takeoff_altitude').value)

        self.dt = 1.0 / control_freq
        self.pre_arm_steps = int(self.PRE_ARM_SECONDS * control_freq)

        if not onnx_path:
            self.get_logger().error('onnx_path parameter is empty — set it in policy.yaml')
            raise RuntimeError('Missing onnx_path')

        # ---- ONNX session ----
        self.get_logger().info(f'Loading ONNX model: {onnx_path}')
        self.session = ort.InferenceSession(
            onnx_path,
            providers=['CPUExecutionProvider'],
        )
        self.gru_hidden = np.zeros((1, 1, 512), dtype=np.float32)  # [n_layers, B, hidden]

        # ---- State ----
        self.pos_enu  = np.zeros(3, dtype=np.float32)
        self.vel_enu  = np.zeros(3, dtype=np.float32)
        self.acc_enu  = np.zeros(3, dtype=np.float32)    # estimated from PX4
        self.heading_yaw = 0.0                            # drone heading (from attitude)
        self.vel_ema_yaw = 0.0                            # velocity-aligned EMA yaw (= Rz)
        self.depth_image = np.ones((9, 16), dtype=np.float32)  # full-range default
        self.step_count  = 0
        self.goal_reached = False

        self.bridge = CvBridge() if HAS_CV_BRIDGE else None

        # ---- QoS matching PX4 uXRCE-DDS ----
        px4_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        # ---- Subscribers ----
        self.create_subscription(
            VehicleLocalPosition, '/fmu/out/vehicle_local_position',
            self._pos_cb, px4_qos)
        self.create_subscription(
            VehicleAttitude, '/fmu/out/vehicle_attitude',
            self._att_cb, px4_qos)
        self.create_subscription(
            Image, depth_topic,
            self._depth_cb, 10)

        # ---- Publishers ----
        self.pub_offboard = self.create_publisher(
            OffboardControlMode, '/fmu/in/offboard_control_mode', 10)
        self.pub_setpoint = self.create_publisher(
            TrajectorySetpoint, '/fmu/in/trajectory_setpoint', 10)
        self.pub_cmd = self.create_publisher(
            VehicleCommand, '/fmu/in/vehicle_command', 10)

        # ---- Control timer ----
        self.create_timer(self.dt, self._control_loop)
        self.get_logger().info(
            f'DiffAero policy node ready. Goal ENU = {self.goal_enu}, '
            f'max_vel = {self.max_vel} m/s')

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _pos_cb(self, msg: VehicleLocalPosition):
        """PX4 local position in NED -> convert to ENU."""
        self.pos_enu = ned_to_enu(np.array([msg.x, msg.y, msg.z],  dtype=np.float32))
        self.vel_enu = ned_to_enu(np.array([msg.vx, msg.vy, msg.vz], dtype=np.float32))
        # ax/ay/az may not always be available; fall back to zero if NaN
        ax = msg.ax if math.isfinite(msg.ax) else 0.0
        ay = msg.ay if math.isfinite(msg.ay) else 0.0
        az = msg.az if math.isfinite(msg.az) else 0.0
        self.acc_enu = ned_to_enu(np.array([ax, ay, az], dtype=np.float32))

    def _att_cb(self, msg: VehicleAttitude):
        """PX4 quaternion [w,x,y,z] in NED -> heading yaw in ENU."""
        self.heading_yaw = quat_px4_to_yaw_enu(msg.q)

    def _depth_cb(self, msg: Image):
        """Decode depth image, resize to 9x16, normalise to [0, 1]."""
        try:
            if self.bridge is not None:
                depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            else:
                # Fallback: assume 32FC1 encoding
                depth = np.frombuffer(msg.data, dtype=np.float32).reshape(msg.height, msg.width)
        except Exception as exc:
            self.get_logger().warn(f'Depth decode error: {exc}', throttle_duration_sec=5.0)
            return

        depth = depth.astype(np.float32)
        # Resize to policy input resolution
        depth = cv2.resize(depth, (16, 9), interpolation=cv2.INTER_NEAREST)
        # Replace NaN / inf with max range, then normalise
        depth = np.nan_to_num(depth, nan=self.max_range, posinf=self.max_range, neginf=0.0)
        self.depth_image = np.clip(depth / self.max_range, 0.0, 1.0)

    # ------------------------------------------------------------------
    # PX4 command helpers
    # ------------------------------------------------------------------

    def _timestamp_us(self) -> int:
        return int(self.get_clock().now().nanoseconds / 1000)

    def _publish_offboard_mode(self):
        msg = OffboardControlMode()
        msg.timestamp  = self._timestamp_us()
        msg.position   = False
        msg.velocity   = True   # we send velocity setpoints
        msg.acceleration = False
        msg.attitude   = False
        msg.body_rate  = False
        self.pub_offboard.publish(msg)

    def _publish_vel_setpoint(self, vel_ned: np.ndarray, yaw: float = float('nan')):
        msg = TrajectorySetpoint()
        msg.timestamp  = self._timestamp_us()
        msg.position   = [float('nan')] * 3
        msg.velocity   = [float(vel_ned[0]), float(vel_ned[1]), float(vel_ned[2])]
        msg.acceleration = [float('nan')] * 3
        msg.yaw        = float(yaw)
        self.pub_setpoint.publish(msg)

    def _send_vehicle_command(self, command: int, param1=0.0, param2=0.0):
        msg = VehicleCommand()
        msg.timestamp       = self._timestamp_us()
        msg.command         = command
        msg.param1          = float(param1)
        msg.param2          = float(param2)
        msg.target_system   = 1
        msg.target_component = 1
        msg.source_system   = 1
        msg.source_component = 1
        msg.from_external   = True
        self.pub_cmd.publish(msg)

    def _arm(self):
        self._send_vehicle_command(
            VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0)
        self.get_logger().info('ARM command sent.')

    def _engage_offboard(self):
        # param2=6 is the custom mode index for offboard in PX4
        self._send_vehicle_command(
            VehicleCommand.VEHICLE_CMD_DO_SET_MODE, param1=1.0, param2=6.0)
        self.get_logger().info('OFFBOARD mode command sent.')

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def _update_vel_ema_yaw(self):
        """
        Track the velocity-aligned yaw used as the local frame definition.
        Matches pmc.yaml: vel_ema_factor=0.1, align_yaw_with_vel_ema=True.
        """
        vel_xy_norm = float(np.linalg.norm(self.vel_enu[:2]))
        if vel_xy_norm > 0.3:  # only update when moving
            raw_yaw = math.atan2(float(self.vel_enu[1]), float(self.vel_enu[0]))
            delta = angle_wrap(raw_yaw - self.vel_ema_yaw)
            self.vel_ema_yaw = angle_wrap(self.vel_ema_yaw + self.vel_ema_alpha * delta)

    def _run_policy(self) -> np.ndarray:
        """
        Run ONNX inference.

        Returns:
            vel_ned: velocity setpoint in NED frame [3].
        """
        self._update_vel_ema_yaw()
        Rz   = yaw_rotation_matrix(self.vel_ema_yaw)   # [3, 3], world->local via Rz.T
        Rz_T = Rz.T

        # ---- target_vel: capped velocity vector toward goal ----
        rel  = self.goal_enu - self.pos_enu              # [3] ENU
        dist = float(np.linalg.norm(rel))
        if dist < 0.3:
            if not self.goal_reached:
                self.get_logger().info(
                    f'Goal reached! dist={dist:.2f} m. Hovering.')
            self.goal_reached = True
            return enu_to_ned(np.zeros(3, dtype=np.float32))

        # clamp magnitude to max_vel (same formula as base_env.target_vel)
        scale = max(dist / self.max_vel, 1.0)
        target_vel_world = (rel / scale).astype(np.float32)  # [3]

        # ---- rotate to local (yaw-only) frame ----
        target_vel_local = (Rz_T @ target_vel_world).astype(np.float32)  # [3]
        vel_local        = (Rz_T @ self.vel_enu).astype(np.float32)       # [3]

        # uz in local frame: for yaw-only Rz, Rz.T @ [0,0,1] = [0,0,1] always.
        # Include for completeness; matches the training env's `dynamics.uz`.
        uz_local = np.array([0., 0., 1.], dtype=np.float32)

        # ---- assemble state vector [1, 9] ----
        state = np.concatenate([target_vel_local, uz_local, vel_local])[None]

        # ---- perception [1, 9, 16] ----
        perception = self.depth_image[None].astype(np.float32)

        # ---- orientation [1, 3]: [roll=0, pitch=0, yaw] ----
        #   Only used inside point_mass_quat() to compute quat_xyzw_cmd;
        #   that output is not sent to PX4, so approximate heading suffices.
        orientation = np.array([[0., 0., self.vel_ema_yaw]], dtype=np.float32)

        # ---- action bounds [1, 3] ----
        min_action = np.array([[-self.max_acc_xy, -self.max_acc_xy, 0.]], dtype=np.float32)
        max_action = np.array([[ self.max_acc_xy,  self.max_acc_xy, self.max_acc_z]],
                               dtype=np.float32)

        # ---- ONNX inference ----
        ort_inputs = {
            'state':      state,
            'perception': perception,
            'orientation': orientation,
            'Rz':         Rz[None],          # [1, 3, 3]
            'min_action': min_action,
            'max_action': max_action,
            'hidden_in':  self.gru_hidden,   # [1, 1, 512]
        }
        outputs = self.session.run(None, ort_inputs)
        # outputs: [action[1,3], quat_xyzw_cmd[1,4], acc_norm[1], hidden_out[1,1,512]]
        acc_world_enu   = outputs[0][0].astype(np.float32)   # [3] ENU world-frame accel
        self.gru_hidden = outputs[3].astype(np.float32)      # [1, 1, 512]

        # ---- integrate acceleration to velocity (Euler, capped) ----
        vel_cmd_enu = (self.vel_enu + acc_world_enu * self.dt).astype(np.float32)
        speed = float(np.linalg.norm(vel_cmd_enu))
        if speed > self.max_vel * 1.5:
            vel_cmd_enu *= (self.max_vel * 1.5 / speed)

        return enu_to_ned(vel_cmd_enu)

    # ------------------------------------------------------------------
    # Main control loop
    # ------------------------------------------------------------------

    def _control_loop(self):
        # Always publish offboard mode heartbeat first (PX4 requires this)
        self._publish_offboard_mode()
        self.step_count += 1

        # ---- Arm and engage offboard after pre-arm period ----
        if self.step_count == self.pre_arm_steps:
            self._arm()
        if self.step_count == self.pre_arm_steps + 5:   # 5 steps after arm
            self._engage_offboard()

        if self.goal_reached:
            # Hover in place
            self._publish_vel_setpoint(np.zeros(3, dtype=np.float32))
            return

        # ---- Takeoff phase: ascend to target altitude before navigating ----
        current_alt = float(self.pos_enu[2])
        if current_alt < self.takeoff_alt - 0.2:
            vel_ned = enu_to_ned(
                np.array([0., 0., min(1.5, self.takeoff_alt - current_alt)],
                         dtype=np.float32))
            self._publish_vel_setpoint(vel_ned)
            return

        # ---- Policy inference ----
        try:
            vel_ned = self._run_policy()
        except Exception as exc:
            self.get_logger().error(f'Policy inference failed: {exc}', throttle_duration_sec=1.0)
            self._publish_vel_setpoint(np.zeros(3, dtype=np.float32))
            return

        self._publish_vel_setpoint(vel_ned)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args=None):
    rclpy.init(args=args)
    try:
        node = DiffAeroPolicyNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
