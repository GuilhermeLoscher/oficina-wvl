// ======================================
// OFICINA WVL - app.js
// ======================================

let itens_mao = [];
let itens_pecas = [];

// ======================================
// ADICIONAR ITEM
// ======================================

function adicionarItem(){

    const mao =
        document.getElementById('mao').value.trim();

    const peca =
        document.getElementById('peca').value.trim();

    const valor_mao =
        parseFloat(
            document.getElementById('valor_mao').value
        ) || 0;

    const valor_peca =
        parseFloat(
            document.getElementById('valor_peca').value
        ) || 0;

    // MÃO DE OBRA
    if(mao){

        itens_mao.push({
            descricao: mao,
            valor: valor_mao
        });

    }

    // PEÇAS
    if(peca){

        itens_pecas.push({
            descricao: peca,
            valor: valor_peca
        });

    }

    atualizarLista();
    atualizarTotal();
    limparCampos();

}

// ======================================
// ATUALIZAR LISTA
// ======================================

function atualizarLista(){

    const lista =
        document.getElementById('lista');

    lista.innerHTML = '';

    // TÍTULO MÃO DE OBRA
    if(itens_mao.length > 0){

        lista.innerHTML += `
            <div class="secao-titulo verde">
                🔧 MÃO DE OBRA
            </div>
        `;

    }

    // ITENS MÃO DE OBRA
    itens_mao.forEach((item, index)=>{

        lista.innerHTML += `
            <div class="item">
                <div>
                    ${item.descricao}
                </div>

                <div>
                    R$ ${item.valor.toFixed(2)}
                </div>
            </div>
        `;

    });

    // TÍTULO PEÇAS
    if(itens_pecas.length > 0){

        lista.innerHTML += `
            <div class="secao-titulo azul">
                🧩 PEÇAS
            </div>
        `;

    }

    // ITENS PEÇAS
    itens_pecas.forEach((item, index)=>{

        lista.innerHTML += `
            <div class="item">
                <div>
                    ${item.descricao}
                </div>

                <div>
                    R$ ${item.valor.toFixed(2)}
                </div>
            </div>
        `;

    });

}

// ======================================
// TOTAL
// ======================================

function atualizarTotal(){

    let total = 0;

    itens_mao.forEach(item=>{
        total += item.valor;
    });

    itens_pecas.forEach(item=>{
        total += item.valor;
    });

    document.getElementById('total')
        .innerHTML =
        `TOTAL: R$ ${total.toFixed(2)}`;

}

// ======================================
// LIMPAR CAMPOS
// ======================================

function limparCampos(){

    document.getElementById('mao').value = '';
    document.getElementById('peca').value = '';

    document.getElementById('valor_mao').value = '';
    document.getElementById('valor_peca').value = '';

}

// ======================================
// NOVO ORÇAMENTO
// ======================================

function novo(){

    itens_mao = [];
    itens_pecas = [];

    atualizarLista();
    atualizarTotal();

    document.getElementById('cliente').value = '';
    document.getElementById('telefone').value = '';
    document.getElementById('veiculo').value = '';
    document.getElementById('placa').value = '';

    limparCampos();

}

// ======================================
// GERAR PDF
// ======================================

async function gerarPDF(){

    const cliente =
        document.getElementById('cliente').value;

    if(!cliente){

        alert('Informe o cliente');

        return;

    }

    const dados = {

        cliente: cliente,

        telefone:
            document.getElementById('telefone').value,

        veiculo:
            document.getElementById('veiculo').value,

        placa:
            document.getElementById('placa').value,

        data:
            document.getElementById('data').value,

        itens_mao: itens_mao,

        itens_pecas: itens_pecas

    };

    try{

        const resposta =
            await fetch('/gerar_pdf', {

                method: 'POST',

                headers: {
                    'Content-Type': 'application/json'
                },

                body: JSON.stringify(dados)

            });

        const resultado =
            await resposta.json();

        if(resultado.arquivo){

            window.open(
                `/download/${resultado.arquivo}`,
                '_blank'
            );

        }else{

            alert('Erro ao gerar PDF');

        }

    }catch(erro){

        console.error(erro);

        alert('Erro no servidor');

    }

}

// ======================================
// HISTÓRICO
// ======================================

async function abrirHistorico(){

    try{

        const resposta =
            await fetch('/historico');

        const dados =
            await resposta.json();

        if(dados.length === 0){

            alert('Nenhum orçamento encontrado');

            return;

        }

        let texto = '';

        dados.forEach(item=>{

            texto +=
`
CLIENTE: ${item[0]}
VEÍCULO: ${item[1]}
PLACA: ${item[2]}
TOTAL: R$ ${item[3]}
DATA: ${item[4]}

`;

        });

        alert(texto);

    }catch(erro){

        console.error(erro);

        alert('Erro ao carregar histórico');

    }

}

// ======================================
// SERVICE WORKER
// ======================================

if('serviceWorker' in navigator){

    window.addEventListener('load', ()=>{

        navigator.serviceWorker.register(
            '/static/service-worker.js'
        )
        .then(registro=>{

            console.log(
                'Service Worker registrado'
            );

        })
        .catch(erro=>{

            console.log(
                'Erro Service Worker',
                erro
            );

        });

    });

}

// ======================================
// DATA AUTOMÁTICA
// ======================================

window.onload = ()=>{

    const hoje = new Date();

    const ano = hoje.getFullYear();

    let mes =
        String(
            hoje.getMonth() + 1
        ).padStart(2,'0');

    let dia =
        String(
            hoje.getDate()
        ).padStart(2,'0');

    document.getElementById('data').value =
        `${ano}-${mes}-${dia}`;

};