#include <stdlib.h>

void overwrite(int *ptr) {
    // Out of bounds write via aliased pointer
    ptr[10] = 42; 
}

int main() {
    int buffer[5];
    int *alias = buffer;
    
    overwrite(alias);
    
    return 0;
}