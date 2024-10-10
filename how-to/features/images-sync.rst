Images Sync
===========

This feature deploys Openstack Images Sync, a tool for synchronizing
images from a SimpleStreams source to Sunbeam.

[note type=“info”] **Note:** This feature is currently only supported in
channel ``2024.1/edge`` of the **openstack** snap. [/note]

Enable Images Sync
------------------

To enable Images Sync, run the following command:

::

   sunbeam enable images-sync

Disable Images Sync
-------------------

To disable Images Sync, run the following command:

::

   sunbeam disable images-sync

[note type=“caution”] **Caution**: Disabling Images Sync will **not**
remove synchronized images from Glance (the underlying OpenStack image
service). [/note]

Usage
-----

Users need the role ``reader`` to list images.

To list images added by the Images Sync feature, run the following
command:

::

   openstack image list | grep auto-sync/

Sample output:

::

   | 200df230-0983-4cd8-9d14-97327664f77b | auto-sync/ubuntu-focal-20.04-amd64-server-20240513-disk1.img   | active |
   | 1935961b-e646-4f0d-a796-8c653308f790 | auto-sync/ubuntu-jammy-22.04-amd64-server-20240514-disk1.img   | active |
   | 62be8807-f068-4317-9552-c1357fa8d962 | auto-sync/ubuntu-noble-24.04-amd64-server-20240523.1-disk1.img | active |

The feature downloads images for the three most recent LTS releases.
