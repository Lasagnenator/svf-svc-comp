#include "stdlib.h"

void func(int *ptr) {
    (*ptr) = 1;
}

int main() {
    int *ptr = NULL;

    func(ptr);

}