#/bin/bash

if [[ -e './dist' ]]; then
    zip -r "dist.$(date +%F.%H.%M.%S).zip" dist
fi

mkdir -p ./dist/userScripts
rm -fr dist/userScripts/*
cp userScripts/*.sh dist/userScripts
cp userScripts/*.py dist/userScripts