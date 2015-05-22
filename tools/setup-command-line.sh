#! /usr/bin/env bash

if [ "$1" == "" ] ; then

	py=`echo "$0" | sed 's/sh$/py/'`
	python -i "$py"
	
else

	echo "Setup command line with some imports and kml data"
	
fi