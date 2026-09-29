import gssapi
ctx = gssapi.SecurityContext(
    name=gssapi.Name("namenode@REALM.COM", gssapi.NameType.hostbased_service),
    usage="initiate",
)
print("gssapi SecurityContext OK:", type(ctx).__name__)
from hdfs.ext.kerberos import KerberosClient
c = KerberosClient("http://nn:50070", timeout=10)
print("hdfs KerberosClient OK (带 gssapi 原生后端)")
