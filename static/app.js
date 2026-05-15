let itens_mao = [];
let itens_pecas = [];

function adicionarItem(){

    const mao =
        document.getElementById('mao').value.trim();

    const peca =
        document.getElementById('peca').value.trim();

    const valor_mao =
        parseFloat(document.getElementById('valor_mao').value) || 0;

    const valor_peca =
        parseFloat(document.getElementById('valor_peca').value) || 0;

    if(mao){
        itens_mao.push({descricao: mao, valor: valor_mao});
    }

    if(peca){
        itens_pecas.push({descricao: peca, valor: valor_peca});
    }

    atualizarLista();
    atualizarTotal();

}

function atualizarLista(){

    const lista = document.getElementById('lista');
    lista.innerHTML = '';

    itens_mao.forEach(i=>{
        lista.innerHTML += `
            <div class="item">🔧 ${i.descricao} - R$ ${i.valor.toFixed(2)}</div>
        `;
    });

    itens_pecas.forEach(i=>{
        lista.innerHTML += `
            <div class="item">🧩 ${i.descricao} - R$ ${i.valor.toFixed(2)}</div>
        `;
    });

}

function atualizarTotal(){

    let total = 0;

    itens_mao.forEach(i=> total += i.valor);
    itens_pecas.forEach(i=> total += i.valor);

    document.getElementById('total').innerText =
        `TOTAL: R$ ${total.toFixed(2)}`;

}

async function gerarPDF(){

    const cliente =
        document.getElementById('cliente').value;

    if(!cliente){
        alert('Informe o cliente');
        return;
    }

    const dados = {
        cliente,
        telefone: document.getElementById('telefone').value,
        veiculo: document.getElementById('veiculo').value,
        placa: document.getElementById('placa').value,
        data: document.getElementById('data').value,
        itens_mao,
        itens_pecas
    };

    try{

        const res = await fetch('/gerar_pdf', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify(dados)
        });

        const r = await res.json();

        if(r.arquivo){

            // 🔥 CORREÇÃO IPHONE
            window.location.href = `/download/${r.arquivo}`;

        }else{
            alert('Erro ao gerar PDF');
        }

    }catch(e){
        alert('Erro no servidor');
    }
}

function novo(){

    itens_mao = [];
    itens_pecas = [];

    atualizarLista();
    atualizarTotal();

}

async function abrirHistorico(){

    const res = await fetch('/historico');
    const data = await res.json();

    let texto = '';

    data.forEach(i=>{
        texto += `${i[0]} | ${i[1]} | ${i[2]} | R$ ${i[3]} | ${i[4]}\n\n`;
    });

    alert(texto);

}