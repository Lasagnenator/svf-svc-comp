#include <stdlib.h>

void fun(int arg) {
    char *ptr = malloc(sizeof(char));

    if (arg > 5) {
        free(ptr);
    }

    (*ptr) = 'a';
}

int main(int argc, char **argv) {
    fun(argc);
}