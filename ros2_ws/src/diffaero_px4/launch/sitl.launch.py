"""
Launch file for DiffAero policy deployment with PX4 SITL + Gazebo.

Usage (after building the workspace):
    ros2 launch diffaero_px4 sitl.launch.py

What this launches:
    1. Micro XRCE-DDS Agent  — bridges PX4 uORB <-> ROS 2 DDS
    2. ros_gz_bridge          — bridges Gazebo Ignition sensor topics -> ROS 2
    3. diffaero_policy node   — runs ONNX inference and sends setpoints to PX4

PX4 SITL + Gazebo must be started separately (see setup_sitl.sh):
    cd PX4-Autopilot
    PX4_SYS_AUTOSTART=4020 PX4_GZ_MODEL=x500_depth \\
        PX4_GZ_WORLD=obstacle_field \\
        ./build/px4_sitl_default/bin/px4 -s etc/init.d-posix/rcS
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess, DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory('diffaero_px4')
    config_file = os.path.join(pkg, 'config', 'policy.yaml')

    onnx_path_arg = DeclareLaunchArgument(
        'onnx_path',
        default_value=os.path.join(
            os.path.expanduser('~'),
            'Desktop/diffaero/outputs/train/2026-04-09/19-45-56/checkpoints/exported_actor.onnx'),
        description='Path to exported_actor.onnx')

    # ------------------------------------------------------------------
    # 1. Micro XRCE-DDS Agent (PX4 <-> ROS 2 bridge)
    #    Connects to PX4 on UDP port 8888 (default SITL port).
    # ------------------------------------------------------------------
    xrce_agent = ExecuteProcess(
        cmd=['MicroXRCEAgent', 'udp4', '-p', '8888'],
        additional_env={'LD_LIBRARY_PATH': '/usr/local/lib'},
        output='screen',
        name='xrce_dds_agent',
    )

    # ------------------------------------------------------------------
    # 2. ros_gz_bridge: forward depth camera from Ignition -> ROS 2
    #    Topic:  /depth_camera/depth/image_raw
    #    Type:   sensor_msgs/msg/Image  (from gz.msgs.Image)
    # ------------------------------------------------------------------
    gz_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='gz_ros_bridge',
        arguments=[
            '/depth_camera@sensor_msgs/msg/Image[gz.msgs.Image',
            # Bridge clock as well (optional but useful)
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
        ],
        output='screen',
    )

    # ------------------------------------------------------------------
    # 3. DiffAero policy node
    # ------------------------------------------------------------------
    policy_node = Node(
        package='diffaero_px4',
        executable='policy_node',
        name='diffaero_policy',
        parameters=[
            config_file,
            {'onnx_path': LaunchConfiguration('onnx_path')},
        ],
        output='screen',
        emulate_tty=True,
    )

    return LaunchDescription([
        onnx_path_arg,
        xrce_agent,
        gz_bridge,
        policy_node,
    ])
