FROM python:2.7-alpine

RUN apk add --update --no-cache libpq wget python-dev postgresql-dev build-base postgresql
RUN pip install python-dockercloud psycopg2 s3cmd

COPY backup.py /

CMD python /backup.py
