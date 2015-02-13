#
# Enthought product code
#
# (C) Copyright 2013 Enthought, Inc., Austin, TX
# All right reserved.
#

import os.path
from setuptools import setup, find_packages

data = {}
execfile(os.path.join('jigna', '__init__.py'), data)

setup(
    name='jigna',
    version=data['__version__'],
    author='Enthought, Inc',
    author_email='info@enthought.com',
    url='https://github.com/enthought/jigna',
    description='HTML frontend for Traits models.',
    long_description=open('README.rst').read(),
    install_requires=open('requirements.txt').read().split('\n'),
    packages=find_packages(),
    package_dir={'jigna':'jigna'},
    include_package_data=True,
    package_data={'jigna': ['js/dist/*.js']},
    zip_safe=False
)
