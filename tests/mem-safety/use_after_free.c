#include <stdlib.h>

void main() {
    int *ptr = malloc(sizeof(int));
    *ptr = 100;
    
    free(ptr); 
    
    *ptr = 200;
}