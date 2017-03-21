from __future__ import print_function

import dockercloud
import psycopg2
import subprocess
import os
import datetime
import time

# Parameters:
BUCKET = os.environ['S3_BUCKET']
NAMESPACE = os.environ['S3_NAMESPACE']
ACCESS_KEY = os.environ['AWS_ACCESS_KEY']
SECRET_KEY = os.environ['AWS_SECRET_KEY']
s3cmd = 's3cmd --access_key="%s" --secret_key="%s"' % (ACCESS_KEY, SECRET_KEY)
bucket_prefix = 's3://%s/db_backups/%s' % (BUCKET, NAMESPACE)


def get_latest_md5(db_name, table):
    cmd = '%s ls %s/%s/%s/' % (s3cmd, bucket_prefix, db_name, table)
    current_files = subprocess.Popen(['/bin/sh', '-c', cmd], stdout=subprocess.PIPE)
    current_files, _ = current_files.communicate()
    current_files = current_files.split('\n')
    current_files = [line.split() for line in current_files if line.strip() != '']
    current_files.sort(key=lambda line: line[0]+' '+line[1])
    if len(current_files) == 0:
        return None
    else:
        return current_files[-1][-1].split('.')[-3]  # the md5 hash


def handle_table(db_url, table):
    start = time.time()
    db_name = db_url.split('/')[-1]
    print('\tGot table "%s/%s"' % (db_name, table))
    latest_hash = get_latest_md5(db_name, table)
    print('\tExisting hash "%s"' % latest_hash)
    cmd = 'pg_dump -t "%s" "%s" | gzip | md5sum' % (table, db_url)
    # print('#',cmd)
    proc = subprocess.Popen(['/bin/sh', '-c', cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    current_hash, _ = proc.communicate()
    current_hash = current_hash.split()[0][:6]
    print('\tCurrent hash "%s"' % (current_hash, ))
    if latest_hash is None:
        status = 'NEW'
    elif current_hash != latest_hash:
        status = 'MODIFIED'
    else:
        status = 'SAME'
    if status != 'SAME':
        filename = '%s/%s/%s/%s.%s.%s.%s.pg_dump.gz' % \
                   (bucket_prefix, db_name, table, db_name, table, datetime.datetime.now().date().isoformat(), current_hash)
        cmd = '%s put --no-progress --no-encrypt - %s' % (s3cmd, filename)
        cmd = 'pg_dump -t "%s" "%s" | gzip | %s ' % \
              (table, db_url, cmd)
        # print('#',cmd)
        proc = subprocess.Popen(['/bin/sh', '-c', cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate()
        print(out, err)
        # print('-->', proc.returncode)
    print('\tTable %s: %s, %d secs' % (table, status, int(time.time() - start)))


def handle_db(db_url):
    start = time.time()
    print('Encountered DB URL %s' % db_url)
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    cursor.execute("""SELECT table_name FROM information_schema.tables
                      WHERE table_schema = 'public'""")
    count = 0
    for table in cursor.fetchall():
        table = table[0]
        handle_table(db_url, table)
        count += 1
    print('\tDB %s: %d tables, %d secs' % (db_url, count, int(time.time() - start)))


def get_services():
    all_urls = set()
    services = dockercloud.Service().list()
    for service in services:
        service = service.fetch(service.pk)
        attrs = service.get_all_attributes()
        # for attr in attrs.items(): print attr
        envvars = attrs['calculated_envvars']
        for envvar in envvars:
            if envvar['key'] == 'DATABASE_URL':
                db_url = envvar['value']
                if db_url not in all_urls:
                    handle_db(db_url)
                    all_urls.add(db_url)

if __name__ == "__main__":
    get_services()
