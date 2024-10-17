#include <stdlib.h>

int main() {
    int *arr = malloc(5 * sizeof(int));
    // Don't free

    return 0;
}
