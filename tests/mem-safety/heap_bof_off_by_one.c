#include <stdlib.h>

int main() {
    int *arr = malloc(5 * sizeof(int));
    if (arr == NULL) return 1;

    // Off-by-one error: writes to arr[5] which is out of bounds
    for (int i = 0; i <= 5; i++) {
        arr[i] = i * 10;
    }

    free(arr);
    return 0;
}