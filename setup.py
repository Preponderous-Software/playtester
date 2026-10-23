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
    url="https://github.com/Preponderous-Software/playtester",
    license="MIT",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    package_data={"playtester": ["data/*/*", "data/*/*/*"]},
    include_package_data=True,
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: X11 Applications",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Games/Entertainment",
        "Topic :: Software Development :: Testing",
    ],
    # The agent playtest kit (pt, playtester.harness, playtester.agents) is
    # standard-library Python. What it needs besides is system software, which
    # pip cannot install: Xvfb, xdotool, ImageMagick (import), and Mesa's
    # llvmpipe for games that render with OpenGL. On Debian/Ubuntu:
    #   sudo apt-get install xvfb xdotool imagemagick libgl1-mesa-dri
    install_requires=[],
    extras_require={
        # The experimental screenshot automation framework (GameAutomator and
        # friends): pip install "playtester[automation]". pynput pulls in evdev,
        # which builds a C extension on Linux.
        "automation": [
            "pillow>=10.0.0",
            "pyautogui>=0.9.54",
            "pynput>=1.7.6",
        ],
    },
    entry_points={
        "console_scripts": [
            "pt=playtester.harness.cli:main",
            "playtester=playtester.harness.cli:main",
        ],
    },
)
