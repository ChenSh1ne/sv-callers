#!/usr/bin/env python

import os
import sys


user, start, end = sys.argv[1:4] # start/end  in YY-MM-DD
os.environ["SLURM_TIME_FORMAT"] = "standard"
sep = ","
csvfile = "jobs.csv"
sqlfile = "create_db.sql"
dbfile = "jobs.db"
stmts = """
CREATE TABLE {0} (
    jobid,
    jobname,
    submit,
    start,
    end,
    cputimeraw,
    mem,
    reqcpus,
    nodelist,
    state
);

.separator {1}
.import {2} {0}

DELETE FROM {0} WHERE jobid = 'JobID';
-- post-processing {0} table (assumes submission via xenon-cli)
UPDATE {0} SET jobid=REPLACE(jobid, '.batch', '');
UPDATE {0} SET jobname=REPLACE(jobname, 'batch', '');

CREATE TABLE {3} AS
SELECT
    CAST(jobid AS INTEGER) AS jobid,
    GROUP_CONCAT(jobname, '') AS jobname,
    submit,
    start,
    end,
    CAST(cputimeraw AS INTEGER) AS cputime, -- in sec
    MAX(CAST(REPLACE(mem, 'K', '') AS INTEGER) / 1024) AS mem_mb,
    MIN(CAST(reqcpus AS INTEGER)) AS reqcpus,
    nodelist,
    state
FROM {0}
GROUP BY jobid;

CREATE INDEX idx_{3}_jobid ON {3}(jobid);
CREATE INDEX idx_{3}_jobname ON {3}(jobname);

CREATE VIEW {4} AS
SELECT
    jobid,
    jobname,
    strftime('%Y-%m-%d %H:%M:%S', submit) AS subtime,
    strftime('%Y-%m-%d %H:%M:%S', start) AS stime,
    strftime('%Y-%m-%d %H:%M:%S', end) AS etime,
    strftime('%s',start) - strftime('%s', submit) AS qtime, -- in sec
    strftime('%s',end) - strftime('%s', start) AS runtime,  -- in sec
    cputime,
    strftime('%Y-%m-%d %H:00:00', start) AS stime_bin,
    strftime('%Y-%m-%d %H:00:00', end) AS etime_bin,
    mem_mb,
    reqcpus AS n_cores,
    nodelist AS hostname,
    state AS status
FROM {3};

CREATE VIEW {5} AS
SELECT
    jobname,
    COUNT(jobid) AS n_jobs,
    status,
    MIN(runtime) AS min_runtime,
    MAX(runtime) AS max_runtime,
    CAST(ROUND(AVG(runtime)) AS INTEGER) AS mean_runtime,
    MIN(mem_mb) AS min_mem,
    MAX(mem_mb) AS max_mem,
    CAST(ROUND(AVG(mem_mb)) AS INTEGER) AS mean_mem
FROM {4}
GROUP BY jobname, status;

CREATE VIEW {6} AS
SELECT
    etime_bin,
    status,
    COUNT(DISTINCT hostname) AS n_hosts,
    SUM(n_cores) AS n_cores,
    COUNT(*) AS n_jobs
FROM {4}
GROUP BY etime_bin, status ORDER BY 1;

CREATE VIEW {7} AS
SELECT T1.etime_bin, T1.status, T1.n_jobs, SUM(T2.n_jobs) AS cum_jobs
FROM {6} AS T1, {6} AS T2
WHERE T2.rowid <= T1.rowid AND T2.status = T1.status
GROUP BY T1.status, T1.etime_bin, T1.n_jobs
ORDER BY T1.status, T1.rowid;
""".format('TMP', sep, csvfile, 'JOB', 'V_JOB', 'VV_JOB', 'V_JOB_E', 'VV_JOB_E')

with open(sqlfile, "w") as fout:
    fout.write(stmts)

cmd = "sacct -u {} -S {} -E {} -P --delimiter={} \
      -o jobid,jobname,submit,start,end,cputimeraw,maxvmsize,reqcpus,nodelist,state > {} \
      && sqlite3 {} < {}".format(user, start, end, sep, csvfile, dbfile, sqlfile)
os.system(cmd)
