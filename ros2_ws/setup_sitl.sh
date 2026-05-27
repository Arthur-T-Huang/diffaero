#!/usr/bin/env bash
# =============================================================================
#  setup_sitl.sh  —  Complete setup for DiffAero + PX4 SITL + Gazebo Harmonic
# =============================================================================
#
#  Run once to install dependencies, build the workspace, and then launch
#  a Gazebo SITL session with 30 obstacles and the DiffAero policy flying
#  through them.
#
#  Tested on:  Ubuntu 24.04, ROS 2 Jazzy, PX4 main, Gazebo Harmonic
#  Requirements: curl, git, pip3
#
#  Usage:
#    chmod +x setup_sitl.sh
#    ./setup_sitl.sh [--skip-install]   # first run without flag
#    ./setup_sitl.sh --launch-only      # after everything is installed
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIFFAERO_ROOT="$(dirname "$SCRIPT_DIR")"
WS_DIR="$SCRIPT_DIR"              # ros2_ws/

ONNX_PATH="$DIFFAERO_ROOT/outputs/train/2026-04-09/19-45-56/checkpoints/exported_actor.onnx"
PX4_DIR="$HOME/PX4-Autopilot"
ROS_DISTRO="${ROS_DISTRO:-jazzy}"

SKIP_INSTALL=false
LAUNCH_ONLY=false
for arg in "$@"; do
    case $arg in
        --skip-install) SKIP_INSTALL=true ;;
        --launch-only)  LAUNCH_ONLY=true  ;;
    esac
done

echo "================================================================"
echo "  DiffAero PX4 SITL setup"
echo "  ONNX model : $ONNX_PATH"
echo "  ROS distro : $ROS_DISTRO"
echo "  PX4 dir    : $PX4_DIR"
echo "================================================================"

# ------------------------------------------------------------------ #
#  STEP 1 — Install ROS 2 Jazzy (Ubuntu 24.04)                       #
# ------------------------------------------------------------------ #
if ! $LAUNCH_ONLY && ! $SKIP_INSTALL; then
    if ! command -v ros2 &>/dev/null; then
        echo ">>> Installing ROS 2 $ROS_DISTRO ..."
        sudo apt-get update -y
        sudo apt-get install -y software-properties-common curl gnupg lsb-release
        sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
            -o /usr/share/keyrings/ros-archive-keyring.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
            http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
            | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
        sudo apt-get update -y
        sudo apt-get install -y \
            "ros-$ROS_DISTRO-desktop" \
            "ros-$ROS_DISTRO-ros-gz-bridge" \
            "ros-$ROS_DISTRO-ros-gz-image" \
            "ros-$ROS_DISTRO-cv-bridge" \
            python3-colcon-common-extensions \
            python3-rosdep \
            python3-pip
        sudo rosdep init 2>/dev/null || true
        rosdep update
        echo "source /opt/ros/$ROS_DISTRO/setup.bash" >> ~/.bashrc
    else
        echo ">>> ROS 2 already installed, skipping."
    fi
fi

# ------------------------------------------------------------------ #
#  STEP 2 — Install Gazebo Harmonic                                  #
# ------------------------------------------------------------------ #
if ! $LAUNCH_ONLY && ! $SKIP_INSTALL; then
    if ! command -v gz &>/dev/null; then
        echo ">>> Installing Gazebo Harmonic ..."
        sudo apt-get install -y curl
        sudo curl -sSL https://packages.osrfoundation.org/gazebo.gpg \
            -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] \
            http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
            | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
        sudo apt-get update -y
        sudo apt-get install -y gz-harmonic
    else
        echo ">>> Gazebo already installed, skipping."
    fi
fi

# ------------------------------------------------------------------ #
#  STEP 3 — Clone & build PX4-Autopilot                              #
# ------------------------------------------------------------------ #
if ! $LAUNCH_ONLY && ! $SKIP_INSTALL; then
    if [ ! -d "$PX4_DIR" ]; then
        echo ">>> Cloning PX4-Autopilot main (Ubuntu 24.04 support) ..."
        git clone --branch main --depth 1 \
            https://github.com/PX4/PX4-Autopilot.git "$PX4_DIR"
        cd "$PX4_DIR"
        git submodule update --init --recursive
        bash Tools/setup/ubuntu.sh --no-nuttx
        make px4_sitl_default -j$(nproc)
        echo ">>> PX4 build complete."
    else
        echo ">>> PX4-Autopilot already present at $PX4_DIR, skipping."
    fi
fi

# ------------------------------------------------------------------ #
#  STEP 4 — Install Micro XRCE-DDS Agent                             #
# ------------------------------------------------------------------ #
if ! $LAUNCH_ONLY && ! $SKIP_INSTALL; then
    if ! command -v MicroXRCEAgent &>/dev/null; then
        echo ">>> Installing Micro XRCE-DDS Agent ..."
        pip3 install --user pyros-genmsg
        git clone --depth 1 \
            https://github.com/eProsima/Micro-XRCE-DDS-Agent.git /tmp/xrce_agent
        mkdir -p /tmp/xrce_agent/build
        cmake -S /tmp/xrce_agent -B /tmp/xrce_agent/build
        sudo cmake --build /tmp/xrce_agent/build --target install -j$(nproc)
        echo ">>> Micro XRCE-DDS Agent installed."
    else
        echo ">>> MicroXRCEAgent already installed, skipping."
    fi
fi

# ------------------------------------------------------------------ #
#  STEP 5 — Clone px4_msgs and build the ROS 2 workspace             #
# ------------------------------------------------------------------ #
if ! $LAUNCH_ONLY; then
    source "/opt/ros/$ROS_DISTRO/setup.bash"

    PX4_MSGS_DIR="$WS_DIR/src/px4_msgs"
    if [ ! -d "$PX4_MSGS_DIR" ]; then
        echo ">>> Cloning px4_msgs ..."
        git clone --branch main --depth 1 \
            https://github.com/PX4/px4_msgs.git "$PX4_MSGS_DIR"
    fi

    echo ">>> Installing Python dependencies for policy node ..."
    pip3 install --user onnxruntime opencv-python

    echo ">>> Building ROS 2 workspace ..."
    cd "$WS_DIR"
    rosdep install --from-paths src --ignore-src -r -y || true
    colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
    echo ">>> Workspace build complete."
fi

source "$WS_DIR/install/setup.bash"

# ------------------------------------------------------------------ #
#  STEP 6 — Copy Gazebo world and model to PX4 search paths          #
# ------------------------------------------------------------------ #
DIFFAERO_PKG_SHARE="$WS_DIR/install/diffaero_px4/share/diffaero_px4"

WORLDS_DEST="$PX4_DIR/Tools/simulation/gz/worlds"
MODELS_DEST="$PX4_DIR/Tools/simulation/gz/models"

if [ -d "$WORLDS_DEST" ]; then
    echo ">>> Copying obstacle_field.sdf to PX4 worlds ..."
    cp "$DIFFAERO_PKG_SHARE/worlds/obstacle_field.sdf" "$WORLDS_DEST/"
fi
if [ -d "$MODELS_DEST" ]; then
    echo ">>> Copying iris_depth_camera model to PX4 models ..."
    cp -r "$DIFFAERO_PKG_SHARE/models/iris_depth_camera" "$MODELS_DEST/"
fi

# ------------------------------------------------------------------ #
#  STEP 7 — Launch everything                                         #
# ------------------------------------------------------------------ #
echo ""
echo "================================================================"
echo "  All dependencies ready.  Launching SITL + policy node ..."
echo "================================================================"
echo ""
echo "  This will open THREE processes:"
echo "    1. PX4 SITL + Gazebo (obstacle_field world, iris_depth_camera)"
echo "    2. Micro XRCE-DDS Agent"
echo "    3. ROS 2 policy node (ros_gz_bridge + diffaero_policy)"
echo ""
echo "  You can monitor the drone in Gazebo GUI."
echo "  Press Ctrl+C to stop all processes."
echo ""

# Terminal 1: PX4 SITL
gnome-terminal --title="PX4 SITL" -- bash -c "
    source /opt/ros/$ROS_DISTRO/setup.bash
    cd $PX4_DIR
    PX4_SYS_AUTOSTART=4001 \
    PX4_GZ_MODEL=iris_depth_camera \
    PX4_GZ_WORLD=obstacle_field \
    ./build/px4_sitl_default/bin/px4 build/px4_sitl_default/etc/init.d-posix/rcS
    exec bash" &

sleep 3  # give PX4 time to start

# Terminal 2: ROS 2 launch (bridge + policy)
gnome-terminal --title="ROS 2 Policy" -- bash -c "
    source /opt/ros/$ROS_DISTRO/setup.bash
    source $WS_DIR/install/setup.bash
    ros2 launch diffaero_px4 sitl.launch.py onnx_path:=$ONNX_PATH
    exec bash" &

echo ""
echo ">>> Launched! Check the Gazebo window for the drone."
echo ">>> Topics you can monitor:"
echo "    ros2 topic echo /fmu/out/vehicle_local_position"
echo "    ros2 topic echo /fmu/in/trajectory_setpoint"
echo "    ros2 topic hz /depth_camera/depth/image_raw"
wait
