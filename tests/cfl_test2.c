void reach_error(){}

void foo(){
    reach_error();
}

void bar(){
    foo();
}

int main(){
    bar();
}