from setuptools import setup, find_packages

setup(
    name="brainstem_python_api_tools",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "requests",
        "jupyter",
    ],
    author="BrainSTEM Team",
    author_email="petersen.peter@gmail.com",
    description="A Python toolset for interacting with API of BrainSTEM.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/brainstem-org/brainstem_python_api_tools",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)
