#include <stdlib.h>

int main() {
    int *data = malloc(4 * sizeof(int));
    if (!data) return 1;
    
    int *cursor = data;
    
    // Move cursor 5 times (writes 5 integers into space meant for 4)
    for(int i = 0; i < 5; i++) {
        *cursor = i;
        cursor++;
    }
    
    free(data);
    return 0;
}