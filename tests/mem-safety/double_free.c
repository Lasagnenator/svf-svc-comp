#include <stdlib.h>

void main() {
    char *ptr = malloc(sizeof(char));
    
    free(ptr);
    free(ptr);
}