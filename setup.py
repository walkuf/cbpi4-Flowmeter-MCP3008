from setuptools import setup

# read the contents of your README file
from os import path
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(name='cbpi4-Flowmeter-MCP3008',
      version='0.0.6',
      description='CraftBeerPi4 Flowsensor MCP3008 / Step Plugin ',
      author='Rick Walkup',
      author_email='walkuf@gmail.com',
      url='https://github.com/walkuf/cbpi4-Flowmeter-MCP3008',
      include_package_data=True,
      keywords='globalsettings',
      package_data={
        # If any package contains *.txt or *.rst files, include them:
      '': ['*.txt', '*.rst', '*.yaml'],
      'cbpi4-Flowmeter-MCP3008': ['*','*.txt', '*.rst', '*.yaml']},
      packages=['cbpi4-Flowmeter-MCP3008'],
      install_requires=[
          'cbpi4>=4.1.10.rc2'
      ],
      long_description=long_description,
      long_description_content_type='text/markdown'
     )
