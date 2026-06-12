from setuptools import find_packages, setup


setup(
    name="sdata-a",
    version="0.1.0",
    description="GitHub-native satellite news intelligence pipeline architecture.",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.9",
    install_requires=["PyYAML>=6.0.1"],
    extras_require={"dev": ["pytest>=8.0.0", "ruff>=0.6.0"]},
)
