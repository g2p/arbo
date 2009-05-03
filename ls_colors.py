#!/usr/bin/python -S
# vim: set fileencoding=utf-8 sw=2 ts=2 et :
from __future__ import absolute_import

# http://git.savannah.gnu.org/gitweb/?p=coreutils.git;a=blob;f=src/dircolors.c;h=7dad7fd9b829d796e2f2339167851f14a94b960a;hb=master#l70
# http://git.savannah.gnu.org/gitweb/?p=coreutils.git;a=blob;f=src/ls.c;h=795d1edcadf0c67030b5469c6c8763a9f2bd771f;hb=master#l536
ls_codes = [
    ( 'lc', '\033[', [ 'LEFT', 'LEFTCODE', ], ),
    ( 'rc', 'm', [ 'RIGHT', 'RIGHTCODE', ], ),
    ( 'ec', '', [ 'END', 'ENDCODE', ], ),
    ( 'rs', '0', [ 'RESET', ], ),
    ( 'no', '', [ 'NORMAL', 'NORM', ], ),
    ( 'fi', '', [ 'FILE', ], ),
    ( 'di', '01;34', [ 'DIR', ], ),
    ( 'ln', '01;36', [ 'LNK', 'LINK', 'SYMLINK', ], ),
    ( 'pi', '33', [ 'FIFO', 'PIPE', ], ),
    ( 'so', '01;35', [ 'SOCK', ], ),
    ( 'bd', '01;33', [ 'BLK', 'BLOCK', ], ),
    ( 'cd', '01;33', [ 'CHR', 'CHAR', ], ),
    ( 'mi', '', [ 'MISSING', ], ),
    ( 'or', '', [ 'ORPHAN', ], ),
    ( 'ex', '01;32', [ 'EXEC', ], ),
    ( 'do', '01;35', [ 'DOOR', ], ),
    ( 'su', '37;41', [ 'SUID', 'SETUID', ], ),
    ( 'sg', '30;43', [ 'SGID', 'SETGID', ], ),
    ( 'st', '37;44', [ 'STICKY', ], ),
    ( 'ow', '34;42', [ 'OTHER_WRITABLE', 'OWR', ], ),
    ( 'tw', '30;42', [ 'STICKY_OTHER_WRITABLE', 'OWT', ], ),
    ( 'ca', '30;41', [ 'CAPABILITY', ], ),
    ( 'hl', '44;37', [ 'HARDLINK', ], ),
    ( 'cl', '\033[K', [ 'CLRTOEOL', ], ),
    ]


