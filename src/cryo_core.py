import sys
import os
import subprocess

def set_frozen_state(freeze):
    if os.geteuid() != 0:
        print("ERRO CRÍTICO: Requer privilégios de root!")
        sys.exit(1)

    is_currently_frozen = os.path.ismount("/media/root-ro")

    if is_currently_frozen:
        subprocess.run(["mount", "-o", "remount,rw", "/media/root-ro"], check=False)
        config_file = "/media/root-ro/etc/overlayroot.conf"
    else:
        config_file = "/etc/overlayroot.conf"

    try:
        lines = []
        if os.path.exists(config_file):
            with open(config_file, "r") as file:
                lines = file.readlines()

        new_lines = []
        found = False
        
        # A MÁGICA ACONTECE AQUI: tmpfs:swap=1 libera o uso da sua partição de 22GB!
        target_value = 'overlayroot="tmpfs:swap=1"\n' if freeze else 'overlayroot=""\n'

        for line in lines:
            if "overlayroot=" in line:
                new_lines.append(target_value)
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(target_value)

        with open(config_file, "w") as file:
            file.writelines(new_lines)
            file.flush()
            os.fsync(file.fileno())
        
        if is_currently_frozen:
            subprocess.run(["mount", "-o", "remount,ro", "/media/root-ro"], check=False)

        estado = "CONGELADO" if freeze else "DESCONGELADO"
        print(f"SUCESSO: Configurado como {estado}.")
        sys.exit(0)
        
    except Exception as e:
        print(f"ERRO: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ["freeze", "thaw"]:
        sys.exit(1)
    
    comando = sys.argv[1]
    set_frozen_state(freeze=(comando == "freeze"))