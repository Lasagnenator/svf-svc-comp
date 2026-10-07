#include <stdlib.h>

struct Data {
    int id;
    char *name;
};

int main() {
    struct Data *d = malloc(sizeof(struct Data));
    if (d == NULL) return 1;
    
    int *id_ptr = &(d->id);
    *id_ptr = 1;

    free(d);

    // Use-after-free through the aliased struct field pointer
    *id_ptr = 2; 
    
    return 0;
}