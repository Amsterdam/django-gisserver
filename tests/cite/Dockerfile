FROM ogccite/ets-wfs20

ENV WFS_SERVER=http://host.docker.internal:8000/wfs/

COPY entrypoint.sh /
ENTRYPOINT ["/entrypoint.sh"]

CMD ["java", "-jar", "/usr/local/tomcat/webapps/teamengine/WEB-INF/lib/ets-wfs20-1.43.jar", "/root/properties.xml"]
