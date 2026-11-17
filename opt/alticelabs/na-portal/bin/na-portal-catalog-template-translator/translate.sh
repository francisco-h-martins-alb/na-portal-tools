#!/bin/sh

#------------------------------------------------------------------------------#
#JAVA_HOME=/opt/alticelabs/libs/jdk6
JAVA_OPTS="-Xms64m -Xmx512m"
LIBS=/opt/alticelabs/na-portal/lib/na-portal-catalog-template-translator/*
LOGS=file:/opt/alticelabs/na-portal/conf/na-portal-catalog-template-translator/log4j.properties
#------------------------------------------------------------------------------#

. /etc/profile.d/java.sh

# VM debug options
# JAVA_OPTS="$JAVA_OPTS -XX:+PrintGC -XX:+PrintGCDetails -XX:+PrintGCTimeStamps -XX:+TraceClassLoading -XX:+TraceClassUnloading -Xloggc:/tmp/gc.log"
# VM options
JAVA_OPTS="$JAVA_OPTS -XX:NewRatio=2 -XX:MaxTenuringThreshold=15"
MACHINE_TYPE=$(uname -m)
if [ ${MACHINE_TYPE} == 'x86_64' ]; then
  JAVA_OPTS="$JAVA_OPTS -XX:+UseCompressedOops"
fi

APP_OPTS="-Dfile.encoding=UTF-8"

$JAVA_HOME/bin/java -cp "$LIBS" $APP_OPTS -Dlog4j.configuration=$LOGS pt.ptinovacao.naportal.catalog.TemplateTranslator "$@"