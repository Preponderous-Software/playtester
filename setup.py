from setuptools import setup, find_packages

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="playtester",
    version="0.2.0",
    description="Game playtesting by parallel AI agents, and an AI game automation framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Daniel McCoy Stephenson",
    url="https://github.com/dmccoystephenson/playtester",
    license="MIT",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    package_data={"playtester": ["data/*/*", "data/*/*/*"]},
    include_package_data=True,
    python_requires=">=3.8",
    install_requires=[
        "pillow>=10.0.0",
        "pyautogui>=0.9.54",
        "pynput>=1.7.6",
    ],
    extras_require={
        # The agent playtest harness (pt) is standard-library Python; what it
        # needs besides is system software, which pip cannot install:
        #   Xvfb, xdotool, ImageMagick (import), and Mesa's llvmpipe for games
        #   that render with OpenGL. On Debian/Ubuntu:
        #   sudo apt-get install xvfb xdotool imagemagick libgl1-mesa-dri
        # This extra exists so `pip install playtester[headless]` documents
        # that intent; it adds no Python packages.
        "headless": [],
    },
    entry_points={
        "console_scripts": [
            "pt=playtester.harness.cli:main",
            "playtester=playtester.harness.cli:main",
        ],
    },
)
