/* Uruchamia proces z listą dopuszczonych ścieżek i odciętym TCP na Linuxie. */
#define _GNU_SOURCE
#include <err.h>
#include <fcntl.h>
#include <linux/landlock.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

static const uint64_t read_access = LANDLOCK_ACCESS_FS_EXECUTE |
    LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR;
static const uint64_t write_access = LANDLOCK_ACCESS_FS_WRITE_FILE |
    LANDLOCK_ACCESS_FS_REMOVE_DIR | LANDLOCK_ACCESS_FS_REMOVE_FILE |
    LANDLOCK_ACCESS_FS_MAKE_CHAR | LANDLOCK_ACCESS_FS_MAKE_DIR |
    LANDLOCK_ACCESS_FS_MAKE_REG | LANDLOCK_ACCESS_FS_MAKE_SOCK |
    LANDLOCK_ACCESS_FS_MAKE_FIFO | LANDLOCK_ACCESS_FS_MAKE_BLOCK |
    LANDLOCK_ACCESS_FS_MAKE_SYM | LANDLOCK_ACCESS_FS_REFER |
    LANDLOCK_ACCESS_FS_TRUNCATE;

static void allow_path(int rules, const char *path, bool writable)
{
    int fd = open(path, O_PATH | O_CLOEXEC);
    if (fd == -1)
        err(1, "%s", path);
    struct stat info;
    if (fstat(fd, &info) == -1)
        err(1, "fstat %s", path);

    uint64_t access = read_access;
    if (writable)
        access |= write_access;
    if (!S_ISDIR(info.st_mode))
        access &= LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_READ_FILE |
            LANDLOCK_ACCESS_FS_WRITE_FILE | LANDLOCK_ACCESS_FS_TRUNCATE;

    struct landlock_path_beneath_attr rule = {
        .allowed_access = access,
        .parent_fd = fd,
    };
    if (syscall(SYS_landlock_add_rule, rules, LANDLOCK_RULE_PATH_BENEATH, &rule, 0) == -1)
        err(1, "landlock_add_rule %s", path);
    close(fd);
}

int main(int argc, char **argv)
{
    int version = syscall(SYS_landlock_create_ruleset, NULL, 0, LANDLOCK_CREATE_RULESET_VERSION);
    if (version < 4)
        errx(1, "Wymagany Linux z Landlock ABI 4 lub nowszym");
    struct landlock_ruleset_attr config = {
        .handled_access_fs = read_access | write_access,
        .handled_access_net = LANDLOCK_ACCESS_NET_BIND_TCP | LANDLOCK_ACCESS_NET_CONNECT_TCP,
    };
    int rules = syscall(SYS_landlock_create_ruleset, &config, sizeof(config), 0);
    if (rules == -1)
        err(1, "landlock_create_ruleset");
    int arg = 1;
    for (; arg + 1 < argc && strcmp(argv[arg], "--") != 0; arg += 2) {
        bool writable = strcmp(argv[arg], "-w") == 0;
        if (!writable && strcmp(argv[arg], "-r") != 0)
            errx(1, "Użycie: restrict-linux [-r ŚCIEŻKA|-w ŚCIEŻKA]... -- KOMENDA");
        allow_path(rules, argv[arg + 1], writable);
    }
    if (arg + 1 >= argc || strcmp(argv[arg], "--") != 0)
        errx(1, "Brak komendy po --");
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == -1)
        err(1, "PR_SET_NO_NEW_PRIVS");
    if (syscall(SYS_landlock_restrict_self, rules, 0) == -1)
        err(1, "landlock_restrict_self");
    close(rules);
    execvp(argv[arg + 1], argv + arg + 1);
    err(1, "%s", argv[arg + 1]);
}
