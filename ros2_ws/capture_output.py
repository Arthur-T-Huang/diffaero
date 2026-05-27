#!/usr/bin/env python3
"""
Capture visual output from the running SITL pipeline:
  1. Depth camera frames from /depth_camera/depth/image_raw  (saved as PNG)
  2. Drone position/velocity log over time
  3. Screenshot of the Gazebo window (via xwd + PIL)

Run after the pipeline is up:
    source /opt/ros/jazzy/setup.bash
    source ~/Desktop/diffaero/ros2_ws/install/setup.bash
    python3 capture_output.py
"""

import os, sys, time, subprocess, threading
import numpy as np
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from sensor_msgs.msg import Image
from px4_msgs.msg import VehicleLocalPosition, TrajectorySetpoint

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "log/sitl_run/capture")
os.makedirs(OUTPUT_DIR, exist_ok=True)

N_FRAMES   = 30     # depth frames to save
CAPTURE_HZ = 2      # depth frames per second to save


class CaptureNode(Node):
    def __init__(self):
        super().__init__('capture_node')

        px4_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST, depth=1)

        self.frame_count  = 0
        self.pos_log      = []
        self.last_depth_t = 0.0
        self.done         = False

        self.create_subscription(Image, '/depth_camera',
                                 self._depth_cb, 10)
        self.create_subscription(VehicleLocalPosition,
                                 '/fmu/out/vehicle_local_position',
                                 self._pos_cb, px4_qos)
        self.create_subscription(TrajectorySetpoint,
                                 '/fmu/in/trajectory_setpoint',
                                 self._setpoint_cb, 10)
        self.get_logger().info(
            f'Capture node ready. Saving {N_FRAMES} frames to {OUTPUT_DIR}')

    def _depth_cb(self, msg):
        now = time.time()
        if now - self.last_depth_t < 1.0 / CAPTURE_HZ:
            return
        self.last_depth_t = now

        depth = np.frombuffer(msg.data, dtype=np.float32).reshape(msg.height, msg.width)
        depth = np.nan_to_num(depth, nan=5.0, posinf=5.0)
        depth_norm = np.clip(depth / 5.0, 0, 1)

        # Upscale 16x9 → 320x180 for visibility, apply colormap
        vis = cv2.resize((depth_norm * 255).astype(np.uint8), (320, 180),
                         interpolation=cv2.INTER_NEAREST)
        vis_color = cv2.applyColorMap(vis, cv2.COLORMAP_PLASMA)
        cv2.putText(vis_color, f'Frame {self.frame_count:03d}  max={depth.max():.1f}m',
                    (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255,255,255), 1)

        path = os.path.join(OUTPUT_DIR, f'depth_{self.frame_count:03d}.png')
        cv2.imwrite(path, vis_color)
        self.frame_count += 1

        if self.frame_count >= N_FRAMES:
            self.get_logger().info(f'Saved {N_FRAMES} depth frames to {OUTPUT_DIR}')
            self.done = True

    def _pos_cb(self, msg):
        self.pos_log.append({
            't':  msg.timestamp / 1e6,
            'x':  msg.x, 'y':  msg.y, 'z':  msg.z,
            'vx': msg.vx,'vy': msg.vy,'vz': msg.vz,
        })

    def _setpoint_cb(self, msg):
        pass  # just confirm setpoints are arriving

    def save_pos_log(self):
        if not self.pos_log:
            return
        path = os.path.join(OUTPUT_DIR, 'position_log.csv')
        with open(path, 'w') as f:
            f.write('t,x,y,z,vx,vy,vz\n')
            for r in self.pos_log:
                f.write(f"{r['t']:.3f},{r['x']:.3f},{r['y']:.3f},{r['z']:.3f},"
                        f"{r['vx']:.3f},{r['vy']:.3f},{r['vz']:.3f}\n")
        print(f'Position log saved to {path}  ({len(self.pos_log)} rows)')


def grab_gazebo_screenshot():
    """Capture the Gazebo window using xwd + PIL."""
    try:
        from PIL import Image as PILImage
        # xwd dumps the first window whose name matches (requires DISPLAY)
        xwd_out = subprocess.check_output(
            ['xwd', '-display', ':0', '-root', '-silent'],
            timeout=5)
        import io
        img = PILImage.open(io.BytesIO(xwd_out))
        path = os.path.join(OUTPUT_DIR, 'gazebo_screenshot.png')
        img.save(path)
        print(f'Gazebo screenshot saved to {path}')
        return path
    except Exception as e:
        print(f'Screenshot failed: {e}')
        return None


def make_depth_montage():
    """Combine saved depth frames into a single montage image."""
    frames = sorted([f for f in os.listdir(OUTPUT_DIR) if f.startswith('depth_')])
    if not frames:
        return
    imgs = [cv2.imread(os.path.join(OUTPUT_DIR, f)) for f in frames[:16]]
    imgs = [i for i in imgs if i is not None]
    if not imgs:
        return
    # Arrange in a 4-row grid
    cols = 4
    rows = (len(imgs) + cols - 1) // cols
    # Pad to fill grid
    while len(imgs) < rows * cols:
        imgs.append(np.zeros_like(imgs[0]))
    grid_rows = [np.hstack(imgs[i*cols:(i+1)*cols]) for i in range(rows)]
    montage = np.vstack(grid_rows)
    path = os.path.join(OUTPUT_DIR, 'depth_montage.png')
    cv2.imwrite(path, montage)
    print(f'Depth montage saved to {path}  ({len(frames)} frames)')
    return path


def main():
    rclpy.init()
    node = CaptureNode()

    print('Waiting for depth frames and position data ...')
    deadline = time.time() + 60  # 60 s timeout

    while not node.done and time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)

    node.save_pos_log()
    node.destroy_node()
    rclpy.shutdown()

    # Post-process
    make_depth_montage()
    grab_gazebo_screenshot()

    print('\nCapture complete. Output files:')
    for f in sorted(os.listdir(OUTPUT_DIR)):
        size = os.path.getsize(os.path.join(OUTPUT_DIR, f))
        print(f'  {f}  ({size//1024} KB)')


if __name__ == '__main__':
    main()
