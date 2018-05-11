from . import config

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.ext.automap import automap_base

Base = automap_base()
Engine = create_engine("mysql://" + config.db_user + ":" + config.db_password + \
                       "@" + config.db_host+ ":" + str(config.db_port) + "/" + config.db_name)

def get_db_base_and_session():
    Base.prepare(Engine, reflect=True)
    session = Session(Engine)
    return (Base, session)