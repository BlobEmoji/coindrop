coindrop
========

Bot to manage special event coin dropping in the Blob Emoji server.

Requires Python 3.8+ and Postgres 12+

Usage
------

First, clone this repository (or download an iteration of it from the ZIP download).

Copy ``config.example.toml`` to ``config.toml``, and edit it to contain your token and any other parameters for your instance.

Next, create a named virtual docker volume that will be used to store the data from PostgreSQL:

.. code:: sh

    docker volume create --name coindrop-postgresql -d local

We do this as opposed to using a host volume because host volumes require permission and ownership emulation which `entirely prevents <https://forums.docker.com/t/volume-binds-issue/17218/4>`__ the creation of this docker network on Windows hosts.

Once the volume has been created, we can simply start up the network:

.. code:: sh

    docker-compose up
