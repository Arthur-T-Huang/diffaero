from setuptools import setup, find_packages
import os
from glob import glob

package_name = 'diffaero_px4'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.py')),
        (os.path.join('share', package_name, 'config'),
            glob('config/*.yaml')),
        (os.path.join('share', package_name, 'worlds'),
            glob('worlds/*.sdf')),
        (os.path.join('share', package_name, 'models', 'iris_depth_camera'),
            glob('models/iris_depth_camera/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='user',
    maintainer_email='user@example.com',
    description='DiffAero SHA2C+RCNN obstacle-avoidance policy for PX4 SITL',
    license='MIT',
    entry_points={
        'console_scripts': [
            'policy_node = diffaero_px4.policy_node:main',
        ],
    },
)
