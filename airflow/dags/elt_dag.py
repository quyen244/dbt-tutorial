from datetime import datetime, timedelta
from airflow import DAG 

from docker.types import Mount 
from airflow.providers.standard.operators.python import PythonOperator 
from airflow.providers.standard.operators.bash import BashOperator 
from airflow.providers.docker.operators.docker import DockerOperator 
import subprocess

default_args = {
    'owner' : 'airflow',
    'depends_on_past' : False,
    'email_on_failure' : False,
    'email_on_retry' : False,
}


def run_elt_script():
    sript_path = "/opt/airflow/elt/elt_script.py"
    result = subprocess.run(
        ["python" , sript_path], capture_output= True, text = True
    )

    if result.returncode != 0:
        raise Exception(f"Script failed with error : {result.stderr}")
    else:
        print(result.stdout)

dag = DAG(
    'elt_and_dbt',
    default_args = default_args,
    description = 'An ELT workflow and dbt',
    start_date = datetime(2026, 8, 14),
    catchup = False,
)

t1 = PythonOperator(
    task_id = "run_elt_script",
    python_callable = run_elt_script,
    dag = dag
) 

t2 = DockerOperator(
    task_id = 'dbt_run',
    image = 'ghcr.io/dbt-labs/dbt-postgres',
    command = [
        "run",
        "--profiles-dir",
        "/root",
        "--project-dir",
        "/opt/dbt"
    ],
    auto_remove = 'success',
    docker_url = "unix://var/run/docker.sock",
    network_mode = "bridge",
    mounts = [
        Mount(source='D:/Projects/Assignment/DE & DA/elt/first_dbt' , target='/opt/dbt', type='bind'),
        Mount(source='C:/Users/Admin/.dbt' , target='/root', type='bind')
    ],
    dag = dag
)


t1 >> t2 

