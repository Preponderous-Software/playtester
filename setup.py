from setuptools import setup, find_packages

setup(
    name="playtester",
    version="0.1.0",
    description="AI-powered game automation system",
    author="playtester",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "pillow>=10.0.0",
        "pyautogui>=0.9.54",
        "pynput>=1.7.6",
    ],
)
