from .models import engine, SessionLocal, UserRole
from . import models, crud, schemas

def init_db():
    db = SessionLocal()
    
    # Create tables
    print("Creating database tables...")
    models.Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")

    try:
        # Create default organization
        org = crud.get_organization_by_name(db, name="Default Organization")
        if not org:
            print("Creating default organization...")
            org_schema = schemas.OrganizationCreate(name="Default Organization")
            org = crud.create_organization(db, organization=org_schema)
            print(f"Organization '{org.name}' created.")
        else:
            print("Default organization already exists.")

        # Create admin user
        admin = crud.get_user_by_username(db, username="admin")
        if not admin:
            print("Creating admin user...")
            user_schema = schemas.UserCreate(
                username="admin",
                password="admin",
                email="admin@example.com",
                role=UserRole.ADMIN,
                organization_id=org.id
            )
            crud.create_user(db, user=user_schema)
            print("Admin user 'admin' with password 'admin' created.")
        else:
            print("Admin user already exists.")

    finally:
        db.close()

if __name__ == "__main__":
    init_db() 