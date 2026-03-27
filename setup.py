from setuptools import setup, find_packages

setup(
    name="pbots-shadow",
    version="0.1.0",
    description="Competitive intelligence system for Polymarket trading bots",
    author="Rug-P",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "requests>=2.31.0",
        "pyyaml>=6.0.1",
        "rich>=13.7.0",
        "click>=8.1.7",
        "pandas>=2.1.0",
        "python-dateutil>=2.8.2",
    ],
    entry_points={
        "console_scripts": [
            "shadow=tools.shadow_cli:cli",
        ],
    },
)
