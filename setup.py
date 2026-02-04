"""Issue Tracker CLI - 安装配置."""

from setuptools import setup, find_packages
from pathlib import Path

# 读取 README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

# 读取版本
version_file = Path(__file__).parent / "src" / "issue_tracker" / "__version__.py"
version_vars = {}
if version_file.exists():
    exec(version_file.read_text(encoding="utf-8"), version_vars)
    VERSION = version_vars.get("__version__", "0.1.0")
else:
    VERSION = "0.1.0"

setup(
    name="issue-tracker-cli",
    version=VERSION,
    author="lbwds",
    author_email="imlbwds@gmail.com",
    description="通用 Issue 追踪 CLI 工具，支持 SQLite 存储和 Markdown 导出",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/lbwds/issue-tracker-cli",
    project_urls={
        "Bug Reports": "https://github.com/lbwds/issue-tracker-cli/issues",
        "Source": "https://github.com/lbwds/issue-tracker-cli",
    },
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,
    install_requires=[
        "PyYAML>=6.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "issue-tracker=issue_tracker.cli:main",
        ],
    },
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Bug Tracking",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords="issue tracker cli sqlite markdown development-tools",
    license="MIT",
)
