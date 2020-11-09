from setuptools import setup
setup(
    name = "ubidump",
    version = "1.0.0",
    entry_points = {
        'console_scripts': ['ubidump=ubidump:main'],
    },
    install_requires=[
        "python-lzo>=1.11",
        "crcmod>=1.7",
    ],
    py_modules=['ubidump'],
    author = "Willem Hengeveld",
    author_email = "itsme@xs4all.nl",
    description = "Commandline tool for viewing or extracting UBIFS images.",
    long_description="""
This tool can be used to view or extract the contents of UBIFS images.

View the contents of the `/etc/passwd` file in the filesystem image `image.ubi`:

    ubidump  -c /etc/passwd  image.ubi

List the files in all the volumes in `image.ubi`:

    ubidump  -l  image.ubi

View the contents of b-tree database from the volumes in `image.ubi`:

    ubidump  -d  image.ubi
""",

    license = "MIT",
    keywords = "ubifs commandline",
    url = "https://github.com/nlitsme/ubidump/",
    classifiers = [
        'Environment :: Console',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'Topic :: Utilities',
        'Topic :: Software Development :: Version Control :: Git',
        'Topic :: System :: Filesystems',
    ],
)

