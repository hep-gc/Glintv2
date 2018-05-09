from . import config

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.ext.automap import automap_base


def get_db_base_and_session():
    Base = automap_base()
    engine = create_engine("mysql://" + config.db_user + ":" + config.db_password + \
                           "@" + config.db_host+ ":" + str(config.db_port) + "/" + config.db_name)
    Base.prepare(engine, reflect=True)
    session = Session(engine)
    return (Base, session)