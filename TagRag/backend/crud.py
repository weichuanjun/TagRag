from sqlalchemy.orm import Session
from . import models, schemas, auth

# ==================================================================
# User CRUD
# ==================================================================

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(
        username=user.username, 
        hashed_password=hashed_password,
        email=user.email,
        role=user.role,
        organization_id=user.organization_id
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: Session, username: str, password: str):
    user = get_user_by_username(db, username)
    if not user:
        return False
    if not auth.verify_password(password, user.hashed_password):
        return False
    return user

# ==================================================================
# Organization CRUD
# ==================================================================

def get_organization_by_name(db: Session, name: str):
    return db.query(models.Organization).filter(models.Organization.name == name).first()

def create_organization(db: Session, organization: schemas.OrganizationCreate):
    db_org = models.Organization(name=organization.name)
    db.add(db_org)
    db.commit()
    db.refresh(db_org)
    return db_org 