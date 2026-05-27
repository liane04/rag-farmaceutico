"""
Script de seed: cria as contas de utilizador iniciais.

Cria a tabela de utilizadores (se necessario) e insere uma conta de
administrador e uma conta de farmaceutico. As passwords sao lidas do
ficheiro .env (SEED_ADMIN_PASSWORD e SEED_FARMACEUTICO_PASSWORD).

E idempotente: contas que ja existam sao ignoradas.

Uso:
    python -m src.auth.seed
"""

from src.config import SEED_ADMIN_PASSWORD, SEED_FARMACEUTICO_PASSWORD
from src.auth.db import atualizar_password_utilizador, criar_utilizador, inicializar_bd, listar_utilizadores, obter_utilizador
from src.auth.seguranca import gerar_hash_password


# Contas a criar no arranque: (username, papel, password).
CONTAS_INICIAIS = [
    ("admin", "admin", SEED_ADMIN_PASSWORD),
    ("farmaceutico", "farmaceutico", SEED_FARMACEUTICO_PASSWORD),
]


def correr_seed() -> None:
    """Cria a tabela e as contas iniciais que ainda nao existam."""
    inicializar_bd()
    print("Tabela de utilizadores pronta.")

    for username, papel, password in CONTAS_INICIAIS:
        if not password:
            raise RuntimeError(
                f"SEED_{username.upper()}_PASSWORD nao esta definida. "
                "Adiciona a variavel no .env ou no UI do Coolify e reinicia a API."
            )
        if obter_utilizador(username) is not None:
            atualizar_password_utilizador(username, gerar_hash_password(password))
            print(f"  Conta '{username}' ja existe -- password atualizada.")
            continue
        criar_utilizador(username, gerar_hash_password(password), papel)
        print(f"  Conta '{username}' criada (papel: {papel}).")

    print("\nUtilizadores registados:")
    for utilizador in listar_utilizadores():
        print(f"  [{utilizador.id}] {utilizador.username} ({utilizador.papel})")


if __name__ == "__main__":
    correr_seed()
