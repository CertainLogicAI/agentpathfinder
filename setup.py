from setuptools import setup, find_packages

setup(
    name="agentpathfinder",
    version="1.3.0",
    description="Signed, tamper-evident task tracking for AI agents",
    author="CertainLogic",
    url="https://github.com/CertainLogicAI/agentpathfinder",
    packages=find_packages(),
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "pf=scripts.pathfinder_client:main",
        ],
    },
    install_requires=[],
    extras_require={
        "dashboard": ["flask>=2.0.0"],
    },
    license="MIT",
)
