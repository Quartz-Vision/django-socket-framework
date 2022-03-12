import setuptools


with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="django-socket-framework",
    version="0.1.9",
    author="Lia Va",
    description="Socket consumer environment with more systematic methods/events and auth",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages('src/'),
    classifiers=[
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
    package_dir={'': 'src'},
    install_requires=[
        "Django >= 3.1.0",
        "djangorestframework-simplejwt >= 4.4.0",
        "channels >= 3.0.3",
        "channels-redis >= 3.2.0"
    ]
)
