#!/usr/bin/env bash
# =============================================================================
#  install_deps.sh  — System-level dependencies (requires sudo)
#  Run this ONCE in your terminal:
#    cd ~/Desktop/diffaero/ros2_ws
#    bash install_deps.sh
# =============================================================================
set -e

ROS_DISTRO=jazzy
echo ">>> [1/4] Installing ROS 2 $ROS_DISTRO (Ubuntu 24.04) ..."
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
    python3-pip \
    cmake \
    build-essential
sudo rosdep init 2>/dev/null || true
rosdep update
grep -qxF "source /opt/ros/$ROS_DISTRO/setup.bash" ~/.bashrc || \
    echo "source /opt/ros/$ROS_DISTRO/setup.bash" >> ~/.bashrc
echo ">>> ROS 2 $ROS_DISTRO installed."

echo ">>> [2/4] Installing Gazebo Harmonic ..."
sudo curl -sSL https://packages.osrfoundation.org/gazebo.gpg \
    -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] \
    http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
    | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
sudo apt-get update -y
sudo apt-get install -y gz-harmonic
echo ">>> Gazebo Harmonic installed."

echo ">>> [3/4] Installing PX4 dependencies ..."
PX4_DIR="$HOME/PX4-Autopilot"
if [ ! -d "$PX4_DIR" ]; then
    git clone --branch main --depth 1 \
        https://github.com/PX4/PX4-Autopilot.git "$PX4_DIR"
    cd "$PX4_DIR"
    git submodule update --init --recursive
fi
cd "$PX4_DIR"
bash Tools/setup/ubuntu.sh --no-nuttx
echo ">>> PX4 dependencies installed."

echo ">>> [4/4] Building Micro XRCE-DDS Agent ..."
if ! command -v MicroXRCEAgent &>/dev/null; then
    git clone --depth 1 \
        https://github.com/eProsima/Micro-XRCE-DDS-Agent.git /tmp/xrce_agent
    cmake -S /tmp/xrce_agent -B /tmp/xrce_agent/build -DCMAKE_BUILD_TYPE=Release
    cmake --build /tmp/xrce_agent/build -j$(nproc)
    sudo cmake --install /tmp/xrce_agent/build
fi
echo ">>> Micro XRCE-DDS Agent installed."

echo ""
echo "================================================================"
echo "  System dependencies installed successfully."
echo "  Now run:  bash build_and_launch.sh"
echo "================================================================"
