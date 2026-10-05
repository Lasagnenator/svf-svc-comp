#include <stdlib.h>

int main() {
    int *ptr = malloc(10 * sizeof(int));
    if (ptr == NULL) return 1;
    
    // Pointer arithmetic creating an inner pointer
    int *bad_ptr = ptr + 2; 

    // Invalid free (not the base pointer)
    free(bad_ptr); 
    
    // Double free (if the first one is counted, or just a standard free of the base)
    free(ptr);     
    
    return 0;
}