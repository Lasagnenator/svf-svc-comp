void reach_error() {}

void A() {
    reach_error();
}

void B() {
    A();
}

void C() {
    B();
}

int main() {
    C();
}
