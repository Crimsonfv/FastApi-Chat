from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .database import get_db
from .models import Usuario
from .schemas import UsuarioCreate, UsuarioResponse, Token, UsuarioLogin
from .config import settings

# Configuración de encriptación de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Configuración de Bearer token
security = HTTPBearer()

def hash_password(password: str) -> str:
    """Encriptar contraseña"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verificar contraseña"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Crear token JWT"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    """Verificar y decodificar token JWT"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        if username is None:
            return None
        return {"username": username}
    except JWTError:
        return None

def get_user_by_username(db: Session, username: str) -> Optional[Usuario]:
    """Obtener usuario por username"""
    return db.query(Usuario).filter(Usuario.username == username).first()

def get_user_by_email(db: Session, email: str) -> Optional[Usuario]:
    """Obtener usuario por email"""
    return db.query(Usuario).filter(Usuario.email == email).first()

def authenticate_user(db: Session, username: str, password: str) -> Optional[Usuario]:
    """Autenticar usuario"""
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.activo:
        return None
    return user

def create_user(db: Session, user: UsuarioCreate) -> Usuario:
    """Crear nuevo usuario"""
    # Verificar si ya existe el username
    if get_user_by_username(db, user.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El username ya está registrado"
        )
    
    # Verificar si ya existe el email
    if get_user_by_email(db, user.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya está registrado"
        )
    
    # Crear usuario
    hashed_password = hash_password(user.password)
    db_user = Usuario(
        username=user.username,
        email=user.email,
        password_hash=hashed_password,
        rol=user.rol
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Usuario:
    """Dependencia para obtener el usuario actual autenticado"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials
    token_data = verify_token(token)
    if token_data is None:
        raise credentials_exception
    
    username = token_data.get("username")
    user = get_user_by_username(db, username)
    if user is None:
        raise credentials_exception
    
    if not user.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo"
        )
    
    return user

async def get_current_active_user(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    """Dependencia para obtener usuario activo"""
    return current_user

async def get_current_admin_user(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    """Dependencia para obtener usuario administrador"""
    if current_user.rol != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador"
        )
    return current_user

def login_user(db: Session, user_login: UsuarioLogin) -> Token:
    """Login de usuario y generación de token"""
    user = authenticate_user(db, user_login.username, user_login.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UsuarioResponse.model_validate(user)
    )