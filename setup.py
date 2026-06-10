from setuptools import find_packages, setup


setup(
    name="mcp-registry-diff",
    version="0.1.1",
    description="Compare MCP registry snapshots and report risky differences.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="alexzhu0",
    license="MIT",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.9",
    entry_points={"console_scripts": ["mcp-registry-diff=mcp_registry_diff.cli:main"]},
)
