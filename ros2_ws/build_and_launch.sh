#!/usr/bin/env bash
# =============================================================================
#  build_and_launch.sh  — Build PX4, ROS 2 workspace, and launch SITL
#  Run after install_deps.sh completes:
#    bash build_and_launch.sh
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIFFAERO_ROOT="$(dirname "$SCRIPT_DIR")"
WS_DIR="$SCRIPT_DIR"
PX4_DIR="$HOME/PX4-Autopilot"
ROS_DISTRO=jazzy
ONNX_PATH="$DIFFAERO_ROOT/outputs/train/2026-04-09/19-45-56/checkpoints/exported_actor.onnx"

source "/opt/ros/$ROS_DISTRO/setup.bash"

# ---- Build PX4 SITL ----
if [ ! -f "$PX4_DIR/build/px4_sitl_default/bin/px4" ]; then
    echo ">>> Building PX4 SITL (this takes 15-30 min) ..."
    cd "$PX4_DIR"
    make px4_sitl_default -j$(nproc)
fi

# ---- Clone px4_msgs if needed ----
PX4_MSGS_DIR="$WS_DIR/src/px4_msgs"
if [ ! -d "$PX4_MSGS_DIR" ]; then
    echo ">>> Cloning px4_msgs ..."
    git clone --branch main --depth 1 \
        https://github.com/PX4/px4_msgs.git "$PX4_MSGS_DIR"
fi

# ---- Python deps ----
echo ">>> Installing Python deps ..."
pip3 install --user --break-system-packages onnxruntime opencv-python

# ---- Build ROS 2 workspace ----
echo ">>> Building ROS 2 workspace ..."
cd "$WS_DIR"
rosdep install --from-paths src --ignore-src -r -y || true
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release
source "$WS_DIR/install/setup.bash"

# ---- Copy world + model into PX4 search paths ----
PKG_SHARE="$WS_DIR/install/diffaero_px4/share/diffaero_px4"
WORLDS_DEST="$PX4_DIR/Tools/simulation/gz/worlds"
MODELS_DEST="$PX4_DIR/Tools/simulation/gz/models"
[ -d "$WORLDS_DEST" ] && cp "$PKG_SHARE/worlds/obstacle_field.sdf" "$WORLDS_DEST/"
[ -d "$MODELS_DEST" ] && cp -r "$PKG_SHARE/models/iris_depth_camera" "$MODELS_DEST/"

LOG_DIR="$WS_DIR/log/sitl_run"
mkdir -p "$LOG_DIR"

echo ""
echo "================================================================"
echo "  Build complete!  Launching PX4 SITL + ROS 2 policy node ..."
echo "  Logs: $LOG_DIR"
echo "================================================================"

GZ_MODELS="$PX4_DIR/Tools/simulation/gz/models"
GZ_WORLDS="$PX4_DIR/Tools/simulation/gz/worlds"
export DISPLAY="${DISPLAY:-:0}"

# ---- Step 1: Start Gazebo (server + GUI window, DISPLAY=:0) ----
# Run with a clean env — sourcing ROS 2 overwrites LD_LIBRARY_PATH and breaks gz sim.
# -r = run immediately without waiting for play button
env -i \
    HOME="$HOME" \
    DISPLAY="$DISPLAY" \
    PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    GZ_SIM_RESOURCE_PATH="$GZ_MODELS:$GZ_WORLDS" \
    gz sim -r "$GZ_WORLDS/obstacle_field.sdf" > "$LOG_DIR/gz.log" 2>&1 &
GZ_PID=$!
echo ">>> Gazebo started (PID $GZ_PID) — log: $LOG_DIR/gz.log"
echo "    A Gazebo window should appear on your display."

echo ">>> Waiting 8 s for Gazebo to initialise ..."
sleep 8

# ---- Step 2: Start PX4 in standalone mode — connects to running Gazebo ----
# PX4_GZ_STANDALONE=1 tells PX4 NOT to start its own Gazebo instance
(
    export DISPLAY="$DISPLAY"
    export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
    export GZ_SIM_RESOURCE_PATH="$GZ_MODELS:$GZ_WORLDS"
    cd "$PX4_DIR/build/px4_sitl_default"
    PX4_SYS_AUTOSTART=4002 \
    PX4_GZ_MODEL=x500_depth \
    PX4_GZ_WORLD=obstacle_field \
    PX4_GZ_STANDALONE=1 \
    ./bin/px4 -d
) > "$LOG_DIR/px4.log" 2>&1 &
PX4_PID=$!
echo ">>> PX4 started (PID $PX4_PID) — log: $LOG_DIR/px4.log"

echo ">>> Waiting 5 s for PX4 to connect to Gazebo ..."
sleep 5

# ---- Launch ROS 2 bridge + policy node ----
(
    source /opt/ros/$ROS_DISTRO/setup.bash
    source "$WS_DIR/install/setup.bash"
    ros2 launch diffaero_px4 sitl.launch.py onnx_path:="$ONNX_PATH"
) > "$LOG_DIR/ros2.log" 2>&1 &
ROS_PID=$!
echo ">>> ROS 2 policy node started (PID $ROS_PID) — log: $LOG_DIR/ros2.log"

echo ""
echo "  Gazebo GUI opens automatically in its own window."
echo "  Follow live logs with:"
echo "    tail -f $LOG_DIR/px4.log"
echo "    tail -f $LOG_DIR/ros2.log"
echo ""
echo "  Monitor ROS 2 topics (in a new shell, after sourcing ROS 2):"
echo "    source /opt/ros/$ROS_DISTRO/setup.bash"
echo "    source $WS_DIR/install/setup.bash"
echo "    ros2 topic hz /depth_camera"
echo "    ros2 topic echo /fmu/in/trajectory_setpoint"
echo ""
echo "  Press Ctrl+C to stop everything."

# Stream both logs to stdout and wait
trap "kill $GZ_PID $PX4_PID $ROS_PID 2>/dev/null; exit" INT TERM
tail -f "$LOG_DIR/gz.log" "$LOG_DIR/px4.log" "$LOG_DIR/ros2.log" &
wait $PX4_PID
