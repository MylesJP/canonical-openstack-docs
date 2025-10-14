# @depends: tutorial/snippets/get-started-with-openstack.task.sh

# [docs-view:enable-ldap]
sunbeam enable ldap
# [docs-view:enable-ldap-end]

# [docs-exec:enable-ldap]
sg snap_daemon 'sunbeam enable ldap'
# [docs-exec:enable-ldap-end]


# [docs-view:disable-ldap]
sunbeam disable ldap
# [docs-view:disable-ldap-end]

# [docs-exec:disable-ldap]
sg snap_daemon 'sunbeam disable ldap'
# [docs-exec:disable-ldap-end]
