from comgate import Comgate, LangCodes, CurrencyCodes, CountryCodes
from utils import prepare_params

if __name__ == "__main__":
    gate = Comgate(
        merchant="anezka.sk",
        secret="c285467176a92d0f32943a51944698e6",
        test=True
    )

    gate.create(
        country=CountryCodes.SK,
        price=10,
        currency=CurrencyCodes.EUR,
        label="Test transations",
        refId="69421a",
        method="ALL",
        email="padampasam@gmail.com",
        prepareOnly=True,
    )

    print("End")
