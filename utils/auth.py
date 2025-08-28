"""
auth.py
=======

Módulo de autenticación para la aplicación de scouting.

Por ahora simplemente mantiene un diccionario de usuarios y contraseñas
en memoria.  En el futuro se puede sustituir por una verificación
basada en una base de datos segura (por ejemplo, con hashes de
contraseña).
"""

from typing import Dict


def authenticate(username: str, password: str) -> bool:
    """Verifica si el nombre de usuario y la contraseña son correctos.

    Parameters
    ----------
    username : str
        Nombre de usuario introducido.
    password : str
        Contraseña introducida.

    Returns
    -------
    bool
        ``True`` si las credenciales son válidas, ``False`` en caso contrario.
    """
    credentials: Dict[str, str] = {
        "admin": "password123",
        "scout": "c4c0acbd",
    }
    return credentials.get(username) == password


__all__ = ["authenticate"]