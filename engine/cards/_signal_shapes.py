"""Shape validation pra signal types declarados em `detection.signals[*]`.

Helpers privados (módulo `_signal_shapes`) compartilhados entre
`engine/cards/loader.py` (validação CARD-020 no carregamento de
`card.yaml`) e `engine/init.py` (avaliação runtime de signals durante
`forge init`).

Não emitem mensagens user-facing — retornam estrutura parseada ou
`None` quando shape inválida. O caller decide qual gate emitir
(`CARD-020` no loader, score-zero silencioso em init).

Escopo: hoje cobre apenas `gradle-dep`. Sinais futuros mencionados em
SPEC §Non-Goals (`pod-dep`, `npm-dep`, `swift-dep`) ganharão seus
próprios `parse_<type>_coordinate` aqui — local intencionalmente
estreito pra evitar dispersão.
"""

from __future__ import annotations


def parse_gradle_coordinate(coord: object) -> tuple[str, str] | None:
    """Valida e parseia uma coordenada Gradle no shape `<group>:<artifact>`.

    Retorna `(group, artifact)` quando o input é uma string não-vazia
    contendo exatamente um `:`, sem whitespace (qualquer caractere
    `str.isspace()`), e com ambos os lados do `:` não-vazios.

    Retorna `None` em qualquer violação dessas regras. Quem chama é
    responsável por decidir o gate (`CARD-020` no loader; silent
    score-zero em init).

    >>> parse_gradle_coordinate("io.ktor:ktor-client-core")
    ('io.ktor', 'ktor-client-core')
    >>> parse_gradle_coordinate("io.ktor:ktor:core")  # 2 colons
    >>> parse_gradle_coordinate("io.ktor:")
    >>> parse_gradle_coordinate(":artifact")
    >>> parse_gradle_coordinate("io.ktor: ktor-client-core")
    >>> parse_gradle_coordinate("io.ktor:\\tktor-client-core")
    >>> parse_gradle_coordinate("")
    >>> parse_gradle_coordinate(None)
    """
    if not isinstance(coord, str) or not coord:
        return None
    if coord.count(":") != 1:
        return None
    if any(c.isspace() for c in coord):
        return None
    group, _, artifact = coord.partition(":")
    if not group or not artifact:
        return None
    return group, artifact
