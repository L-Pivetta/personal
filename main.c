/******************************************************************************

Welcome to GDB Online.
  GDB online is an online compiler and debugger tool for C, C++, Python, PHP, Ruby, 
  C#, OCaml, VB, Perl, Swift, Prolog, Javascript, Pascal, COBOL, HTML, CSS, JS
  Code, Compile, Run and Debug online from anywhere in world.

*******************************************************************************/
#include <stdio.h>

void print_lista(int *);
void ordina(int *);

int main()
{
    int lista[5];
    
    printf("Inserisci 5 numeri.\n");
    
    for (int i=0; i <  5; i++)
    {
        scanf("%d",&lista[i]);
    }
    
    printf("Hai inserito:\n");
    print_lista(lista);
    ordina(lista);
    printf("Lista ordinata:\n");
    print_lista(lista);

    return 0;
}

void print_lista(int *lista)
{
    for (int i=0; i <  5; i++)
    {
        printf("%d\n",lista[i]);
    }
}

void ordina(int *lisa)
{
    int continua = 1;
    
    for(int i = 0; i < 4; i++)
    {
        continua = 1;
        while (continua)
        {
            for (int j = i+1; j < 4-i; j++)
            {
                if (lisa[i] > lisa[j])
                {
                    int aux = lisa[i];
                    lisa[i] = lisa [j];
                    lisa[j] = aux;
                    continua = 1;
                }
                else continua = 0;
            }
        }
    }
}

